#!/usr/bin/env python3
"""Purge strategy-factory generated strategies and all related historical runtime data."""

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


TARGET_TABLE_QUERIES: dict[str, str] = {
    "strategies": "SELECT COUNT(*) FROM target_strategy_ids",
    "strategy_metrics": "SELECT COUNT(*) FROM strategy_metrics WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_quality_reports": "SELECT COUNT(*) FROM strategy_quality_reports WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_signals": "SELECT COUNT(*) FROM strategy_signals WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_signal_event_snapshots": "SELECT COUNT(*) FROM strategy_signal_event_snapshots WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_candidate_evidence": "SELECT COUNT(*) FROM strategy_candidate_evidence WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR candidate_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_signal_evidence": "SELECT COUNT(*) FROM strategy_signal_evidence WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids)",
    "strategy_trade_positions": "SELECT COUNT(*) FROM strategy_trade_positions WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids)",
    "strategy_trade_position_fills": "SELECT COUNT(*) FROM strategy_trade_position_fills WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids) OR position_id IN (SELECT position_id FROM target_position_ids)",
    "paper_accounts": "SELECT COUNT(*) FROM paper_accounts WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR id IN (SELECT account_id FROM target_account_ids)",
    "paper_orders": "SELECT COUNT(*) FROM paper_orders WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids) OR position_id IN (SELECT position_id FROM target_position_ids)",
    "paper_trades": "SELECT COUNT(*) FROM paper_trades WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids) OR position_id IN (SELECT position_id FROM target_position_ids)",
    "paper_nav": "SELECT COUNT(*) FROM paper_nav WHERE account_id IN (SELECT account_id FROM target_account_ids)",
    "paper_positions": "SELECT COUNT(*) FROM paper_positions WHERE account_id IN (SELECT account_id FROM target_account_ids)",
    "paper_account_snapshots": "SELECT COUNT(*) FROM paper_account_snapshots WHERE account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_incubation_accounts": "SELECT COUNT(*) FROM strategy_incubation_accounts WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_incubation_metrics": "SELECT COUNT(*) FROM strategy_incubation_metrics WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_incubation_pipeline_snapshots": "SELECT COUNT(*) FROM strategy_incubation_pipeline_snapshots WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_promotion_reviews": "SELECT COUNT(*) FROM strategy_promotion_reviews WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_runtime_alerts": "SELECT COUNT(*) FROM strategy_runtime_alerts WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_runtime_controls": "SELECT COUNT(*) FROM strategy_runtime_controls WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_runtime_risk_events": "SELECT COUNT(*) FROM strategy_runtime_risk_events WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_runtime_risk_snapshots": "SELECT COUNT(*) FROM strategy_runtime_risk_snapshots WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    "strategy_task_runs": "SELECT COUNT(*) FROM strategy_task_runs WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_generation_experiments": "SELECT COUNT(*) FROM strategy_generation_experiments WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR parent_strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR generated_strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_elimination_log": "SELECT COUNT(*) FROM strategy_elimination_log WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_projection_snapshots": "SELECT COUNT(*) FROM strategy_projection_snapshots WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_vector_profiles": "SELECT COUNT(*) FROM strategy_vector_profiles WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_vector_profile_store": "SELECT COUNT(*) FROM strategy_vector_profile_store WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_vector_index_items": "SELECT COUNT(*) FROM strategy_vector_index_items WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_vector_index_item_store": "SELECT COUNT(*) FROM strategy_vector_index_item_store WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR item_id IN (SELECT id FROM strategy_vector_index_items WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids))",
    "strategy_status_events": "SELECT COUNT(*) FROM strategy_status_events WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_domain_events": "SELECT COUNT(*) FROM strategy_domain_events WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR (aggregate_type='strategy' AND aggregate_id IN (SELECT strategy_id FROM target_strategy_ids))",
    "strategy_lineage": "SELECT COUNT(*) FROM strategy_lineage WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR parent_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_reviews": "SELECT COUNT(*) FROM strategy_reviews WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    "strategy_subscriptions": "SELECT COUNT(*) FROM strategy_subscriptions WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
}


DELETE_QUERIES: list[tuple[str, str]] = [
    (
        "strategy_vector_index_item_store",
        "DELETE FROM strategy_vector_index_item_store WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR item_id IN (SELECT id FROM strategy_vector_index_items WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids))",
    ),
    (
        "strategy_vector_index_items",
        "DELETE FROM strategy_vector_index_items WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_vector_profile_store",
        "DELETE FROM strategy_vector_profile_store WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR profile_id IN (SELECT id FROM strategy_vector_profiles WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids))",
    ),
    (
        "strategy_vector_profiles",
        "DELETE FROM strategy_vector_profiles WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_trade_position_fills",
        "DELETE FROM strategy_trade_position_fills WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids) OR position_id IN (SELECT position_id FROM target_position_ids)",
    ),
    (
        "strategy_trade_positions",
        "DELETE FROM strategy_trade_positions WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids)",
    ),
    (
        "strategy_signal_evidence",
        "DELETE FROM strategy_signal_evidence WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids)",
    ),
    (
        "strategy_candidate_evidence",
        "DELETE FROM strategy_candidate_evidence WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR candidate_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_signal_event_snapshots",
        "DELETE FROM strategy_signal_event_snapshots WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_signals",
        "DELETE FROM strategy_signals WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "paper_account_snapshots",
        "DELETE FROM paper_account_snapshots WHERE account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "paper_nav",
        "DELETE FROM paper_nav WHERE account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "paper_positions",
        "DELETE FROM paper_positions WHERE account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "paper_trades",
        "DELETE FROM paper_trades WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids) OR position_id IN (SELECT position_id FROM target_position_ids)",
    ),
    (
        "paper_orders",
        "DELETE FROM paper_orders WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids) OR signal_id IN (SELECT signal_id FROM target_signal_ids) OR position_id IN (SELECT position_id FROM target_position_ids)",
    ),
    (
        "strategy_incubation_pipeline_snapshots",
        "DELETE FROM strategy_incubation_pipeline_snapshots WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "strategy_incubation_metrics",
        "DELETE FROM strategy_incubation_metrics WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "strategy_promotion_reviews",
        "DELETE FROM strategy_promotion_reviews WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "strategy_runtime_alerts",
        "DELETE FROM strategy_runtime_alerts WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "strategy_runtime_controls",
        "DELETE FROM strategy_runtime_controls WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "strategy_runtime_risk_events",
        "DELETE FROM strategy_runtime_risk_events WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "strategy_runtime_risk_snapshots",
        "DELETE FROM strategy_runtime_risk_snapshots WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "strategy_incubation_accounts",
        "DELETE FROM strategy_incubation_accounts WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR account_id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "paper_accounts",
        "DELETE FROM paper_accounts WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR id IN (SELECT account_id FROM target_account_ids)",
    ),
    (
        "strategy_task_runs",
        "DELETE FROM strategy_task_runs WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_generation_experiments",
        "DELETE FROM strategy_generation_experiments WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR parent_strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR generated_strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_elimination_log",
        "DELETE FROM strategy_elimination_log WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_projection_snapshots",
        "DELETE FROM strategy_projection_snapshots WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_domain_events",
        "DELETE FROM strategy_domain_events WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR (aggregate_type='strategy' AND aggregate_id IN (SELECT strategy_id FROM target_strategy_ids))",
    ),
    (
        "strategy_status_events",
        "DELETE FROM strategy_status_events WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_lineage",
        "DELETE FROM strategy_lineage WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids) OR parent_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_quality_reports",
        "DELETE FROM strategy_quality_reports WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_metrics",
        "DELETE FROM strategy_metrics WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_reviews",
        "DELETE FROM strategy_reviews WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategy_subscriptions",
        "DELETE FROM strategy_subscriptions WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
    (
        "strategies",
        "DELETE FROM strategies WHERE id IN (SELECT strategy_id FROM target_strategy_ids)",
    ),
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


async def _setup_targets(conn: asyncpg.Connection, *, author_id: str, id_prefix: str) -> dict[str, int]:
    await conn.execute(
        """
        CREATE TEMP TABLE target_strategy_ids AS
        SELECT id::text AS strategy_id
        FROM strategies
        WHERE id LIKE $1 OR author_id = $2
        """,
        f"{id_prefix}%",
        author_id,
    )
    await conn.execute(
        """
        CREATE TEMP TABLE target_account_ids AS
        SELECT DISTINCT id AS account_id
        FROM paper_accounts
        WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)
        UNION
        SELECT DISTINCT account_id
        FROM strategy_incubation_accounts
        WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)
          AND account_id IS NOT NULL
        """,
    )
    await conn.execute(
        """
        CREATE TEMP TABLE target_signal_ids AS
        SELECT DISTINCT id::text AS signal_id
        FROM strategy_signals
        WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)
        """,
    )
    await conn.execute(
        """
        CREATE TEMP TABLE target_position_ids AS
        SELECT DISTINCT position_id::text AS position_id
        FROM strategy_trade_positions
        WHERE strategy_id IN (SELECT strategy_id FROM target_strategy_ids)
           OR account_id IN (SELECT account_id FROM target_account_ids)
           OR signal_id IN (SELECT signal_id FROM target_signal_ids)
        """,
    )
    return {
        "target_strategies": int(await conn.fetchval("SELECT COUNT(*) FROM target_strategy_ids")),
        "target_accounts": int(await conn.fetchval("SELECT COUNT(*) FROM target_account_ids")),
        "target_signals": int(await conn.fetchval("SELECT COUNT(*) FROM target_signal_ids")),
        "target_positions": int(await conn.fetchval("SELECT COUNT(*) FROM target_position_ids")),
    }


async def _collect_counts(conn: asyncpg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, query in TARGET_TABLE_QUERIES.items():
        if await _table_exists(conn, table):
            counts[table] = int(await conn.fetchval(query))
    return counts


def _parse_delete_count(status: str) -> int:
    parts = str(status or "").split()
    try:
        return int(parts[-1])
    except (TypeError, ValueError, IndexError):
        return 0


async def _execute_delete_plan(conn: asyncpg.Connection) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for table, query in DELETE_QUERIES:
        if not await _table_exists(conn, table):
            continue
        deleted[table] = _parse_delete_count(await conn.execute(query))
    return deleted


async def _run(*, author_id: str, id_prefix: str, execute: bool) -> dict[str, Any]:
    _load_env_file(DEFAULT_ENV_FILE)
    conn = await asyncpg.connect(_db_dsn())
    try:
        summary = await _setup_targets(conn, author_id=author_id, id_prefix=id_prefix)
        before_counts = await _collect_counts(conn)
        result: dict[str, Any] = {
            "selector": {
                "author_id": author_id,
                "id_prefix": id_prefix,
            },
            "target_summary": summary,
            "before_counts": before_counts,
            "executed": bool(execute),
        }
        if not execute:
            return result

        async with conn.transaction():
            await conn.execute("DROP TABLE IF EXISTS target_strategy_ids")
            await conn.execute("DROP TABLE IF EXISTS target_account_ids")
            await conn.execute("DROP TABLE IF EXISTS target_signal_ids")
            await conn.execute("DROP TABLE IF EXISTS target_position_ids")
            summary = await _setup_targets(conn, author_id=author_id, id_prefix=id_prefix)
            deleted_counts = await _execute_delete_plan(conn)
            remaining_factory = int(
                await conn.fetchval(
                    "SELECT COUNT(*) FROM strategies WHERE id LIKE $1 OR author_id = $2",
                    f"{id_prefix}%",
                    author_id,
                )
            )
            result.update(
                {
                    "target_summary": summary,
                    "deleted_counts": deleted_counts,
                    "remaining_factory_strategies": remaining_factory,
                }
            )
        return result
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge strategy-factory generated strategies and related history.")
    parser.add_argument("--author-id", default="strategy_factory", help="Factory author id selector.")
    parser.add_argument("--id-prefix", default="factory_", help="Factory strategy id prefix selector.")
    parser.add_argument("--execute", action="store_true", help="Actually delete matching data. Defaults to preview only.")
    args = parser.parse_args()

    result = asyncio.run(
        _run(
            author_id=str(args.author_id or "strategy_factory").strip() or "strategy_factory",
            id_prefix=str(args.id_prefix or "factory_").strip() or "factory_",
            execute=bool(args.execute),
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
