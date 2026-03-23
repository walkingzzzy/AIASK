#!/usr/bin/env python3
"""Manual event-driven refresh entrypoint for strategy factory ETL workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for relative in (
    ROOT / "packages" / "akshare-mcp" / "src",
    ROOT / "packages" / "strategy-factory" / "src",
):
    path_str = str(relative)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


async def _run(snapshot_date: str | None) -> dict:
    from akshare_mcp.services import close_shared_runtime_clients
    from akshare_mcp.storage import close_db, get_db
    from strategy_factory import get_local_event_engine

    db = get_db()
    try:
        snapshot = None
        if hasattr(db, "get_daily_snapshot"):
            try:
                snapshot = await db.get_daily_snapshot(snapshot_date)
            except Exception:
                snapshot = None
        if not isinstance(snapshot, dict):
            snapshot = {"date": snapshot_date or str(date.today())}
        snapshot.setdefault("date", snapshot_date or str(date.today()))
        return await get_local_event_engine().refresh(db, snapshot)
    finally:
        await close_shared_runtime_clients()
        await close_db()


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh strategy factory event-driven tables explicitly.")
    parser.add_argument("--snapshot-date", help="Snapshot date in YYYY-MM-DD. Defaults to today/latest snapshot.")
    args = parser.parse_args()

    result = asyncio.run(_run(args.snapshot_date))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
