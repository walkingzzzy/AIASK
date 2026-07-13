#!/usr/bin/env python3
"""Read-only daily formal / evidence / SignalTracker baseline dump.

Usage (from repo root):
  uv run python scripts/ops/runtime_formal_daily.py
  uv run python scripts/ops/runtime_formal_daily.py --db data/db/akshare_mcp.sqlite3 --out reports/ops
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_paths(root: Path) -> None:
    for rel in (
        "packages/akshare-mcp/src",
        "packages/aiask-quant-core/src",
        "packages/strategy-factory/src",
    ):
        path = root / rel
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump read-only factory formal diagnostics")
    parser.add_argument(
        "--db",
        default=os.getenv("AIASK_SQLITE_PATH")
        or os.getenv("AKSHARE_MCP_SQLITE_PATH")
        or "data/db/akshare_mcp.sqlite3",
    )
    parser.add_argument("--out", default="reports/ops")
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args()

    root = _project_root()
    _ensure_paths(root)
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = root / db_path
    if not db_path.exists():
        print(json.dumps({"ok": False, "error": f"db_missing:{db_path}"}, ensure_ascii=False))
        return 2

    from akshare_mcp.services.factory_diagnostics import FactoryDiagnosticsService

    class _Db:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self.connection = conn

    conn = sqlite3.connect(str(db_path))
    try:
        payload = FactoryDiagnosticsService().collect(_Db(conn), top_n=max(1, int(args.top_n)))
    finally:
        conn.close()

    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"runtime_formal_daily_{as_of}.json"
    summary = {
        "date": as_of,
        "db": str(db_path),
        "mode": "read_only",
        "formal_count": payload.get("formal_count"),
        "observe_count": payload.get("observe_count"),
        "orders_total": payload.get("orders_total"),
        "trades_total": payload.get("trades_total"),
        "signals_total": payload.get("signals_total"),
        "signal_tracker": payload.get("signal_tracker"),
        "exit_funnel": payload.get("exit_funnel"),
        "top_blockers": payload.get("top_blockers"),
        "next_actions": payload.get("next_actions"),
        "live_production_claim": False,
        "goal_scope": "runtime_evidence_baseline",
        "diagnostics": payload,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "diagnostics"}, ensure_ascii=False, indent=2))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
