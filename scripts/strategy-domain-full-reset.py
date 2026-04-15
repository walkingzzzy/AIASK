#!/usr/bin/env python3
"""Full reset for strategy/paper-trading domain tables."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import asyncpg


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / "packages" / "akshare-mcp" / ".env"


DELETE_PLAN: list[str] = [
    "strategy_vector_index_item_store",
    "strategy_vector_index_items",
    "strategy_vector_profile_store",
    "strategy_vector_profiles",
    "strategy_trade_position_fills",
    "strategy_trade_positions",
    "strategy_signal_evidence",
    "strategy_candidate_evidence",
    "strategy_signal_event_snapshots",
    "strategy_signals",
    "paper_account_snapshots",
    "paper_nav",
    "paper_positions",
    "paper_trades",
    "paper_orders",
    "strategy_incubation_pipeline_snapshots",
    "strategy_incubation_metrics",
    "strategy_promotion_reviews",
    "strategy_runtime_alerts",
    "strategy_runtime_controls",
    "strategy_runtime_risk_events",
    "strategy_runtime_risk_snapshots",
    "strategy_incubation_accounts",
    "paper_accounts",
    "strategy_task_runs",
    "strategy_generation_experiments",
    "strategy_elimination_log",
    "strategy_projection_snapshots",
    "strategy_domain_events",
    "strategy_status_events",
    "strategy_lineage",
    "strategy_quality_reports",
    "strategy_metrics",
    "strategy_reviews",
    "strategy_subscriptions",
    "strategies",
]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _db_dsn() -> str:
    return (
        f"postgresql://{os.environ.get('DB_USER', 'postgres')}:{os.environ.get('DB_PASSWORD', 'postgres')}"
        f"@{os.environ.get('DB_HOST', '127.0.0.1')}:{os.environ.get('DB_PORT', '5432')}/{os.environ.get('DB_NAME', 'stockdb')}"
    )


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)", f"public.{table}"))


def _parse_delete_count(status: str) -> int:
    parts = str(status or "").split()
    try:
        return int(parts[-1])
    except (TypeError, ValueError, IndexError):
        return 0


async def _collect_counts(conn: asyncpg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in DELETE_PLAN:
        if await _table_exists(conn, table):
            counts[table] = int(await conn.fetchval(f"SELECT COUNT(*) FROM {table}"))
    return counts


async def _run(*, execute: bool) -> dict[str, Any]:
    _load_env_file(DEFAULT_ENV_FILE)
    conn = await asyncpg.connect(_db_dsn())
    try:
        before = await _collect_counts(conn)
        result: dict[str, Any] = {
            "executed": bool(execute),
            "before_counts": before,
        }
        if not execute:
            return result
        deleted: dict[str, int] = {}
        async with conn.transaction():
            for table in DELETE_PLAN:
                if not await _table_exists(conn, table):
                    continue
                deleted[table] = _parse_delete_count(await conn.execute(f"DELETE FROM {table}"))
        after = await _collect_counts(conn)
        result["deleted_counts"] = deleted
        result["after_counts"] = after
        return result
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete all strategy-domain and paper-trading history.")
    parser.add_argument("--execute", action="store_true", help="Actually delete rows. Defaults to preview only.")
    args = parser.parse_args()
    result = asyncio.run(_run(execute=bool(args.execute)))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
