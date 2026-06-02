#!/usr/bin/env python
"""P1-5 remediation: operational-table retention / compaction.

Profiling the live ``akshare_mcp.sqlite3`` (2026-05-29) showed the DB is
~3.27 GB, but the bulk is legitimate market data (``kline_1d`` ~8.7M rows).
The *compactable* growth is unbounded operational/experiment JSON logs:

    strategy_task_runs              ~308 MB  (result JSON per run)
    strategy_generation_experiments ~281 MB  (evaluation/strategy_spec/result)
    strategy_domain_events          ~ 87 MB  (event payloads)

freelist is only ~3 MB, so a full VACUUM reclaims almost nothing -- the fix
is *retention* (age-based pruning of old operational rows) plus incremental
vacuum to return freed pages to the OS. Market-data tables are NEVER touched.

Design / safety:
  * DRY-RUN BY DEFAULT. Nothing is deleted unless ``--apply`` is passed.
  * Each retention rule keeps rows newer than N days (per table ``created_at``
    / ``started_at``), and additionally always keeps the most recent
    ``--min-keep`` rows so a quiet period never empties a table.
  * Before any delete with ``--apply`` it writes a gzip JSON backup of the
    rows to be removed under ``data/backups/`` (override with ``--backup-dir``;
    ``--no-backup`` to skip).
  * Reclaims space with ``PRAGMA incremental_vacuum`` (auto_vacuum is already
    INCREMENTAL). Use ``--full-vacuum`` only in a maintenance window.
  * Market-data / reference tables are hard-excluded; the tool refuses to
    operate on any table not in its allowlist.

Usage:
    python scripts/ops/db_retention.py                 # dry-run report
    python scripts/ops/db_retention.py --apply          # prune + incremental vacuum
    python scripts/ops/db_retention.py --table strategy_task_runs --days 30 --apply
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Per-table retention policy. ts_col is the column used for age comparison.
# Only operational / experiment / event-log tables are eligible. Market-data
# and reference tables are intentionally absent and therefore protected.
RETENTION_RULES: dict[str, dict[str, Any]] = {
    "strategy_task_runs": {"ts_col": "started_at", "days": 45, "min_keep": 2000},
    "strategy_generation_experiments": {"ts_col": "created_at", "days": 60, "min_keep": 2000},
    "strategy_domain_events": {"ts_col": "created_at", "days": 60, "min_keep": 5000},
}

# Hard guard: tables that must never be pruned by this tool.
PROTECTED_TABLES = {
    "kline_1d", "factor_values", "stock_quotes", "financials", "margin_detail",
    "block_stocks", "tdx_relation", "tdx_gpjy_daily", "tdx_bkjy_daily",
    "tdx_consensus", "tdx_stock_extra", "strategies", "strategy_artifacts",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.getenv("AIASK_SQLITE_PATH") or os.getenv("AKSHARE_MCP_SQLITE_PATH")
    if env:
        return Path(env).expanduser().resolve()
    default = REPO_ROOT / "data" / "db" / "akshare_mcp.sqlite3"
    if default.exists():
        return default
    return (Path.home() / ".aiask" / "aiask.sqlite3").resolve()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _cutoff_id(conn: sqlite3.Connection, table: str, ts_col: str, days: int, min_keep: int) -> tuple[int, int]:
    """Return (delete_count, total_count) for rows older than `days` while
    always keeping the newest `min_keep` rows.

    Strategy: find the rowid boundary so that rows with rowid <= boundary are
    candidates for deletion only if (a) older than cutoff AND (b) not within
    the newest min_keep rows.
    """
    total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    if total == 0:
        return 0, 0
    cutoff = f"datetime('now', '-{int(days)} days')"
    # Rows older than cutoff:
    older = conn.execute(
        f'SELECT COUNT(*) FROM "{table}" WHERE "{ts_col}" < {cutoff}'
    ).fetchone()[0]
    # Of those, we must still keep the newest min_keep overall. Deletable =
    # older rows beyond the min_keep most-recent rows.
    deletable = max(0, min(older, total - min_keep))
    return deletable, total


def _delete_old(
    conn: sqlite3.Connection,
    table: str,
    ts_col: str,
    days: int,
    min_keep: int,
    *,
    backup_path: Path | None,
) -> int:
    """Delete old rows. Returns number deleted. Writes backup first if asked."""
    cutoff = f"datetime('now', '-{int(days)} days')"
    # Identify deletable ids: older than cutoff, excluding the newest min_keep
    # rows by rowid (rowid is monotonic with insert order for these tables).
    keep_floor_row = conn.execute(
        f'SELECT rowid FROM "{table}" ORDER BY rowid DESC LIMIT 1 OFFSET ?',
        (min_keep,),
    ).fetchone()
    if keep_floor_row is None:
        return 0  # fewer than min_keep rows: keep all
    keep_floor = keep_floor_row[0]
    select_sql = (
        f'SELECT rowid, * FROM "{table}" '
        f'WHERE "{ts_col}" < {cutoff} AND rowid <= ?'
    )
    rows = conn.execute(select_sql, (keep_floor,)).fetchall()
    if not rows:
        return 0

    if backup_path is not None:
        cols = [d[0] for d in conn.execute(f'SELECT * FROM "{table}" LIMIT 0').description]
        payload = {
            "table": table,
            "exported_at": _now(),
            "row_count": len(rows),
            "columns": ["rowid", *cols],
            "rows": [list(r) for r in rows],
        }
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(backup_path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, default=str)

    conn.execute(
        f'DELETE FROM "{table}" WHERE "{ts_col}" < {cutoff} AND rowid <= ?',
        (keep_floor,),
    )
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIASK operational-table retention (P1-5)")
    parser.add_argument("--db", default=None, help="SQLite path (default: env or data/db/akshare_mcp.sqlite3)")
    parser.add_argument("--table", default=None, help="Limit to one table (must be in the retention allowlist)")
    parser.add_argument("--days", type=int, default=None, help="Override retention window for --table")
    parser.add_argument("--min-keep", type=int, default=None, help="Override min rows kept for --table")
    parser.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    parser.add_argument("--no-backup", action="store_true", help="Skip gzip backup before delete")
    parser.add_argument("--backup-dir", default=None, help="Backup directory (default: data/backups)")
    parser.add_argument("--full-vacuum", action="store_true", help="Run full VACUUM after apply (locks DB; maintenance window only)")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}")
        return 1

    rules = dict(RETENTION_RULES)
    if args.table:
        if args.table not in RETENTION_RULES:
            print(f"ERROR: {args.table!r} is not in the retention allowlist {sorted(RETENTION_RULES)}")
            return 1
        rule = dict(RETENTION_RULES[args.table])
        if args.days is not None:
            rule["days"] = args.days
        if args.min_keep is not None:
            rule["min_keep"] = args.min_keep
        rules = {args.table: rule}

    backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else (REPO_ROOT / "data" / "backups")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{_now()}] db_retention {mode}  db={db_path}")

    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        total_deleted = 0
        for table, rule in rules.items():
            if table in PROTECTED_TABLES:
                print(f"  SKIP protected table {table}")
                continue
            if not _table_exists(conn, table):
                print(f"  SKIP missing table {table}")
                continue
            deletable, total = _cutoff_id(conn, table, rule["ts_col"], rule["days"], rule["min_keep"])
            print(
                f"  {table}: total={total:,} deletable={deletable:,} "
                f"(keep newest {rule['min_keep']:,} & < {rule['days']}d via {rule['ts_col']})"
            )
            if args.apply and deletable > 0:
                backup_path = None if args.no_backup else backup_dir / f"{table}_retention_{stamp}.json.gz"
                deleted = _delete_old(
                    conn, table, rule["ts_col"], rule["days"], rule["min_keep"],
                    backup_path=backup_path,
                )
                conn.commit()
                total_deleted += deleted
                bk = f" backup={backup_path}" if backup_path else " (no backup)"
                print(f"    deleted {deleted:,} rows.{bk}")

        if args.apply and total_deleted > 0:
            if args.full_vacuum:
                print("  running full VACUUM (this locks the DB)...")
                conn.execute("VACUUM")
            else:
                print("  reclaiming pages via PRAGMA incremental_vacuum...")
                conn.execute("PRAGMA incremental_vacuum")
            conn.commit()

        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        print(f"  db main-file size now ~{page_count*page_size/1024/1024:.1f} MB")
    finally:
        conn.close()

    if not args.apply:
        print("DRY-RUN complete. Re-run with --apply to delete (a gzip backup is written first).")
    else:
        print(f"APPLY complete. total_deleted={total_deleted:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
