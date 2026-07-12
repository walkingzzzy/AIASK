#!/usr/bin/env python
"""P1-5 / P2 gate harness: SQLite soak / growth monitor.

Read-only against the DB (PRAGMA + SELECT only). Safe for live soak DBs.

Product path (P2): Agent Intent ``ops.db_soak`` / ``factory.soak_check``
calls ``run_soak()`` with short defaults (single sample). This CLI remains a
thin wrapper for long-running operator soaks.

Usage:
    python scripts/ops/db_soak.py \
        --db data/db/akshare_mcp.sqlite3 \
        --duration-min 360 \
        --interval-sec 300 \
        --max-db-mb 100 \
        --max-row-kb 256 \
        --out reports/ops/db_soak.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MAX_DB_MB = 100.0
DEFAULT_MAX_ROW_KB = 256.0
# Intent path: single sample (duration_min <= 0) unless operator extends.
INTENT_DEFAULT_DURATION_MIN = 0.0
INTENT_MAX_DURATION_MIN = 5.0
INTENT_DEFAULT_INTERVAL_SEC = 1.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_db_path(db: str | Path | None = None) -> Path:
    """Resolve factory SQLite path from explicit arg or env (never invent secrets)."""
    if db is not None and str(db).strip():
        return Path(str(db)).expanduser()
    for key in ("AKSHARE_MCP_SQLITE_PATH", "AIASK_SQLITE_PATH"):
        raw = str(os.getenv(key) or "").strip()
        if raw:
            return Path(raw).expanduser()
    return Path.home() / ".aiask" / "akshare_mcp.sqlite3"


def _db_size_mb(path: Path) -> float:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            total += p.stat().st_size
    return total / 1024 / 1024


def _largest_rows(conn: sqlite3.Connection, top: int = 10) -> list[dict[str, Any]]:
    """Find the largest single rows across user tables (read-only heuristic)."""
    rows: list[dict[str, Any]] = []
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    for table in tables:
        try:
            cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            if not cols:
                continue
            length_expr = " + ".join(f'COALESCE(LENGTH(CAST("{c}" AS BLOB)),0)' for c in cols)
            row = conn.execute(f'SELECT MAX({length_expr}) FROM "{table}"').fetchone()
            max_bytes = int(row[0] or 0)
            rows.append({"table": table, "max_row_bytes": max_bytes})
        except sqlite3.DatabaseError:
            continue
    rows.sort(key=lambda r: r["max_row_bytes"], reverse=True)
    return rows[:top]


def sample(conn: sqlite3.Connection, db_path: Path) -> dict[str, Any]:
    page_count = conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
    auto_vacuum = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
    return {
        "ts": _now(),
        "db_size_mb": round(_db_size_mb(db_path), 3),
        "page_count": page_count,
        "page_size": page_size,
        "freelist_count": freelist,
        "auto_vacuum_mode": auto_vacuum,  # 0=none 1=full 2=incremental
        "largest_rows": _largest_rows(conn),
    }


def run_soak(
    db: str | Path,
    *,
    duration_min: float = 360.0,
    interval_sec: float = 300.0,
    max_db_mb: float = DEFAULT_MAX_DB_MB,
    max_row_kb: float = DEFAULT_MAX_ROW_KB,
    out: str | Path | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run read-only soak sampling. duration_min <= 0 => single sample then exit."""
    db_path = resolve_db_path(db)
    if not db_path.exists():
        return {
            "object": "aiask.ops.db_soak",
            "ok": False,
            "passed": False,
            "dry_run": True,
            "side_effect": "read_only",
            "db": str(db_path),
            "error": f"DB not found: {db_path}",
            "error_code": "DB_NOT_FOUND",
            "breaches": [f"DB not found: {db_path}"],
            "samples": [],
            "sample_count": 0,
        }

    samples: list[dict[str, Any]] = []
    # duration_min <= 0: one sample (product dry-run path)
    effective_duration = float(duration_min)
    deadline = time.monotonic() + max(0.0, effective_duration) * 60.0
    max_row_bytes_allowed = float(max_row_kb) * 1024
    breaches: list[str] = []

    if not quiet:
        print(
            f"[{_now()}] soak start: db={db_path} duration={effective_duration}min "
            f"interval={interval_sec}s"
        )

    while True:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30)
        try:
            s = sample(conn, db_path)
        finally:
            conn.close()
        samples.append(s)

        if s["db_size_mb"] > float(max_db_mb):
            breaches.append(f"db_size {s['db_size_mb']}MB > {max_db_mb}MB at {s['ts']}")
        for r in s["largest_rows"]:
            if r["max_row_bytes"] > max_row_bytes_allowed:
                breaches.append(
                    f"row in {r['table']} = {r['max_row_bytes']}B > "
                    f"{int(max_row_bytes_allowed)}B at {s['ts']}"
                )

        if not quiet:
            print(
                f"[{s['ts']}] size={s['db_size_mb']}MB freelist={s['freelist_count']} "
                f"largest_row={s['largest_rows'][0] if s['largest_rows'] else 'n/a'}"
            )

        # duration_min <= 0: single sample; else stop when wall clock expires
        if effective_duration <= 0 or time.monotonic() >= deadline:
            break
        sleep_for = min(float(interval_sec), max(0.0, deadline - time.monotonic()))
        if sleep_for <= 0:
            break
        time.sleep(sleep_for)

    unique_breaches = sorted(set(breaches))
    result: dict[str, Any] = {
        "object": "aiask.ops.db_soak",
        "ok": True,
        "passed": not unique_breaches,
        "dry_run": True,
        "side_effect": "read_only",
        "db": str(db_path),
        "started": samples[0]["ts"] if samples else None,
        "ended": samples[-1]["ts"] if samples else None,
        "sample_count": len(samples),
        "max_db_mb_observed": max((s["db_size_mb"] for s in samples), default=0.0),
        "thresholds": {"max_db_mb": float(max_db_mb), "max_row_kb": float(max_row_kb)},
        "duration_min": effective_duration,
        "interval_sec": float(interval_sec),
        "breaches": unique_breaches,
        "samples": samples,
        "error": None if not unique_breaches else "soak thresholds breached",
        "error_code": None if not unique_breaches else "SOAK_THRESHOLD_BREACHED",
    }

    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["out"] = str(out_path)
        if not quiet:
            print(f"wrote {out_path}")

    if not quiet:
        if unique_breaches:
            print("SOAK GATE FAILED:")
            for b in unique_breaches:
                print(f"  - {b}")
        else:
            print(
                f"SOAK GATE PASSED: max size {result['max_db_mb_observed']}MB "
                f"over {len(samples)} samples"
            )
    return result


def run_soak_from_params(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Agent Intent entrypoint. Defaults to single-sample dry-run (read-only).

    Long multi-sample soaks stay on the CLI. Intent path only allows multi-sample
    when ``allow_long_soak=true`` and still caps duration at INTENT_MAX_DURATION_MIN.
    """
    payload = dict(params or {})
    db = payload.get("db") or payload.get("db_path") or payload.get("sqlite_path")
    allow_long = bool(payload.get("allow_long_soak") is True or str(payload.get("allow_long_soak") or "").strip().lower() in {"1", "true", "yes", "on"})
    # Product default: one sample. Long loops require explicit opt-in + hard cap.
    if allow_long and payload.get("duration_min") is not None:
        duration_min = float(payload.get("duration_min") or 0.0)
        if duration_min > INTENT_MAX_DURATION_MIN:
            duration_min = INTENT_MAX_DURATION_MIN
    else:
        duration_min = INTENT_DEFAULT_DURATION_MIN
    interval_sec = float(payload.get("interval_sec") or INTENT_DEFAULT_INTERVAL_SEC)
    max_db_mb = float(payload.get("max_db_mb") or DEFAULT_MAX_DB_MB)
    max_row_kb = float(payload.get("max_row_kb") or DEFAULT_MAX_ROW_KB)
    out = payload.get("out")
    result = run_soak(
        resolve_db_path(db),
        duration_min=duration_min,
        interval_sec=interval_sec,
        max_db_mb=max_db_mb,
        max_row_kb=max_row_kb,
        out=out,
        quiet=True,
    )
    # Envelope for Intent executor (success=false only on hard errors, not threshold breach)
    hard_error = result.get("error_code") == "DB_NOT_FOUND"
    return {
        "success": not hard_error,
        "data": result,
        "error": result.get("error") if hard_error else None,
        "error_code": result.get("error_code") if hard_error else None,
        "meta": {
            "side_effect": {"level": "read_only", "writes": False},
            "dry_run": True,
            "object": "aiask.ops.db_soak",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIASK SQLite soak monitor (P1-5 / P2)")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--duration-min", type=float, default=360.0)
    parser.add_argument("--interval-sec", type=float, default=300.0)
    parser.add_argument("--max-db-mb", type=float, default=DEFAULT_MAX_DB_MB)
    parser.add_argument("--max-row-kb", type=float, default=DEFAULT_MAX_ROW_KB)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    db_path = resolve_db_path(args.db)
    result = run_soak(
        db_path,
        duration_min=args.duration_min,
        interval_sec=args.interval_sec,
        max_db_mb=args.max_db_mb,
        max_row_kb=args.max_row_kb,
        out=args.out,
        quiet=False,
    )
    if result.get("error_code") == "DB_NOT_FOUND":
        print(f"ERROR: DB not found: {db_path}")
        return 1
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
