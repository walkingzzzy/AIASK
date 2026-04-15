#!/usr/bin/env python3
"""Recompile/backfill submitted or incubating historical single-name trend strategies."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for relative in (
    ROOT / "packages" / "akshare-mcp" / "src",
    ROOT / "packages" / "strategy-factory" / "src",
):
    path_str = str(relative)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _normalize_limit(value: int | None) -> int | None:
    if value is None:
        return None
    normalized = int(value)
    return normalized if normalized > 0 else None


def _split_csv_tokens(values: list[str] | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        for item in str(value or "").split(","):
            token = item.strip()
            if not token or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    return ordered


def _resolve_strategy_ids(args) -> list[str]:
    return _split_csv_tokens([*(args.strategy_id or []), *(args.strategy_ids or [])])


def _resolve_statuses(args) -> list[str]:
    resolved = _split_csv_tokens(args.statuses or [])
    return resolved or ["submitted", "incubating"]


async def _run_followups(
    db,
    *,
    strategy_ids: list[str],
    recheck_reports: bool,
    replay_submission: bool,
    dry_run: bool,
) -> dict[str, Any]:
    follow_up: dict[str, Any] = {}
    if not strategy_ids:
        return follow_up
    if dry_run:
        if recheck_reports:
            follow_up["review_report_recheck"] = {
                "skipped": True,
                "reason": "dry_run",
                "count": len(strategy_ids),
            }
        if replay_submission:
            follow_up["submission_replay"] = {
                "skipped": True,
                "reason": "dry_run",
                "count": len(strategy_ids),
            }
        return follow_up

    from akshare_mcp.tools.managers.strategy_mgr_lifecycle import (
        handle_review_report_recheck,
        handle_submission_replay,
    )

    if recheck_reports:
        items = []
        for strategy_id in strategy_ids:
            result = await handle_review_report_recheck(db, {"strategy_id": strategy_id})
            items.append(
                {
                    "strategy_id": strategy_id,
                    "success": bool(result.get("success")),
                    "error": result.get("error"),
                    "data": result.get("data"),
                }
            )
        follow_up["review_report_recheck"] = {"count": len(items), "items": items}

    if replay_submission:
        replay = await handle_submission_replay(
            db,
            {
                "strategy_ids": list(strategy_ids),
                "recheck_reports": bool(recheck_reports),
            },
        )
        follow_up["submission_replay"] = {
            "success": bool(replay.get("success")),
            "error": replay.get("error"),
            "data": replay.get("data"),
        }

    return follow_up


async def _run(
    *,
    strategy_ids: list[str],
    statuses: list[str],
    limit: int | None,
    offset: int,
    batch_size: int,
    dry_run: bool,
    force: bool,
    recheck_reports: bool,
    replay_submission: bool,
) -> dict[str, Any]:
    from akshare_mcp.services.strategy_recompile_backfill import backfill_historical_trend_strategies
    from akshare_mcp.storage import close_db, get_db

    db = get_db()
    try:
        result = await backfill_historical_trend_strategies(
            db,
            strategy_ids=strategy_ids or None,
            statuses=statuses or None,
            limit=limit,
            offset=offset,
            batch_size=batch_size,
            dry_run=dry_run,
            force=force,
        )
        followup_ids = [
            str(item.get("strategy_id") or "")
            for item in list(result.get("items") or [])
            if item.get("changed") and item.get("status") == "recompiled"
        ]
        follow_up = await _run_followups(
            db,
            strategy_ids=[item for item in followup_ids if item],
            recheck_reports=recheck_reports,
            replay_submission=replay_submission,
            dry_run=dry_run,
        )
        return {
            **result,
            "strategy_ids": strategy_ids,
            "statuses": statuses,
            "limit": limit,
            "offset": offset,
            "batch_size": batch_size,
            "follow_up": follow_up,
        }
    finally:
        await close_db()


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompile/backfill historical submitted/incubating trend strategies.")
    parser.add_argument(
        "--strategy-id",
        action="append",
        default=[],
        help="Single strategy id. Can be repeated.",
    )
    parser.add_argument(
        "--strategy-ids",
        action="append",
        default=[],
        help="Comma-separated strategy ids. Can be repeated.",
    )
    parser.add_argument(
        "--statuses",
        action="append",
        default=[],
        help="Comma-separated strategy statuses. Defaults to submitted,incubating.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max strategies to process. 0 means no limit.")
    parser.add_argument("--offset", type=int, default=0, help="Offset for paginated scan.")
    parser.add_argument("--batch-size", type=int, default=100, help="Page size when scanning by status.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without persisting updates.")
    parser.add_argument("--force", action="store_true", help="Force overwrite non-empty managed contract fields.")
    parser.add_argument(
        "--recheck-reports",
        action="store_true",
        help="After persisted recompile, refresh review reports for changed recompiled strategies.",
    )
    parser.add_argument(
        "--replay-submission",
        action="store_true",
        help="After persisted recompile, replay submission for changed recompiled strategies.",
    )
    args = parser.parse_args()

    result = asyncio.run(
        _run(
            strategy_ids=_resolve_strategy_ids(args),
            statuses=_resolve_statuses(args),
            limit=_normalize_limit(args.limit),
            offset=max(0, int(args.offset or 0)),
            batch_size=max(1, int(args.batch_size or 100)),
            dry_run=bool(args.dry_run),
            force=bool(args.force),
            recheck_reports=bool(args.recheck_reports),
            replay_submission=bool(args.replay_submission),
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
