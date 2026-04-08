#!/usr/bin/env python3
"""Backfill strategy factory contract and tested-object fields for stored strategies."""

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


def _build_updated_strategy_payload(strategy: dict[str, Any], backfill: dict[str, Any]) -> dict[str, Any]:
    params = dict(strategy.get("params") or {})
    updated_params = {
        **params,
        "candidate_contract_snapshot": dict(backfill.get("candidate_contract_snapshot") or {}),
        "candidate_contract_hash": backfill.get("candidate_contract_hash"),
        "execution_contract_hash": backfill.get("execution_contract_hash"),
        "candidate_identity_signature": backfill.get("candidate_identity_signature"),
        "tested_object_hash": backfill.get("tested_object_hash"),
        "candidate_lineage_contract": dict(backfill.get("candidate_lineage_contract") or {}),
        "target_pool_id": backfill.get("target_pool_id"),
        "logic_signature": backfill.get("logic_signature"),
        "dsl_signature": backfill.get("dsl_signature"),
        "factor_signature": backfill.get("factor_signature"),
        "entry_exit_signature": backfill.get("entry_exit_signature"),
        "legacy_identity_partial": bool(backfill.get("legacy_identity_partial")),
        "tested_object_backfill_incomplete": bool(backfill.get("tested_object_backfill_incomplete")),
    }
    return {
        "id": strategy.get("id"),
        "name": strategy.get("name"),
        "description": strategy.get("description"),
        "author_id": strategy.get("author_id") or "strategy_factory",
        "strategy_type": strategy.get("strategy_type"),
        "params": updated_params,
        "factor_weights": dict(strategy.get("factor_weights") or {}),
        "status": strategy.get("status") or "draft",
        "tags": list(strategy.get("tags") or []),
        "backtest_artifact_id": strategy.get("backtest_artifact_id"),
    }


async def _run(
    *,
    status: str | None,
    limit: int | None,
    offset: int,
    batch_size: int,
    dry_run: bool,
) -> dict[str, Any]:
    from akshare_mcp.storage import close_db, get_db
    from strategy_factory.application.candidate_contract import build_candidate_contract_backfill

    db = get_db()
    scanned = 0
    updated = 0
    unchanged = 0
    incomplete = 0
    saved_ids: list[str] = []
    current_offset = max(0, int(offset or 0))
    remaining = _normalize_limit(limit)

    try:
        while True:
            fetch_limit = min(max(1, int(batch_size or 200)), remaining or max(1, int(batch_size or 200)))
            rows = await db.list_strategies(status=status, limit=fetch_limit, offset=current_offset)
            if not rows:
                break

            for strategy in rows:
                scanned += 1
                backfill = build_candidate_contract_backfill(strategy)
                updated_payload = _build_updated_strategy_payload(strategy, backfill)
                if bool(backfill.get("tested_object_backfill_incomplete")):
                    incomplete += 1
                if dict(updated_payload.get("params") or {}) == dict(strategy.get("params") or {}):
                    unchanged += 1
                else:
                    if not dry_run:
                        await db.save_strategy(updated_payload)
                    updated += 1
                    saved_ids.append(str(strategy.get("id") or ""))

            current_offset += len(rows)
            if remaining is not None:
                remaining -= len(rows)
                if remaining <= 0:
                    break
            if len(rows) < fetch_limit:
                break
    finally:
        await close_db()

    return {
        "status": status,
        "dry_run": dry_run,
        "scanned": scanned,
        "updated": updated,
        "unchanged": unchanged,
        "incomplete": incomplete,
        "updated_strategy_ids": [item for item in saved_ids if item],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill strategy-factory contract/tested-object fields.")
    parser.add_argument("--status", default=None, help="Strategy status filter. Defaults to all statuses.")
    parser.add_argument("--limit", type=int, default=0, help="Max strategies to process. 0 means no limit.")
    parser.add_argument("--offset", type=int, default=0, help="Offset for paginated backfill.")
    parser.add_argument("--batch-size", type=int, default=200, help="Page size for list_strategies.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without persisting updates.")
    args = parser.parse_args()
    resolved_status = None if args.status is None else (str(args.status).strip() or None)

    result = asyncio.run(
        _run(
            status=resolved_status,
            limit=_normalize_limit(args.limit),
            offset=args.offset,
            batch_size=args.batch_size,
            dry_run=bool(args.dry_run),
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
